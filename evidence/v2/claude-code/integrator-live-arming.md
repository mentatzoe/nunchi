# Claude Code V2 integrator live arming — 2026-07-21

This is integrator-owned append evidence. It does not rewrite the delivering
lane's Attempt-6 snapshot or declare acceptance.

## Exact repository objects

- Attempt-6 evidence input: `b12726b9e01739c2faf9027b6ef5038d3cd0c969`.
- Live-source implementation successor:
  `7ea499be33c6260f79e10f07fe77110b147929e2`.
- Branch: `claude/claude-code-v2-integration-3ac219`, pushed to `origin`.
- Installed Claude Code: `2.1.215`.

## Recoverable host transition

Before mutation, `apply-transport-patch.sh --verify` returned exit 2 and the
documented legacy-partial digest
`b025d1c2aa7df54a03fb2b03d403276902959cc13f7327d559a96eb2a91f358b`.
The settings file was copied byte-for-byte to
`/Users/zmll/.claude/settings.json.nunchi-v2-backup-20260721T0219Z`; both
files had SHA-256
`93e8a4564c881387ed7a0553a208c0c9a75473139e600ddadede2186ac85fcfb`
before registration changed.

The reviewed ladder then proved this exact sequence:

1. rollback to pristine `server.ts`:
   `c3c79c6519e23470fcc5f07e38415e50b4f054e42e670e89bd037fa64659e135`;
2. read-only verification returned exit 1, `PRISTINE BASE 0.0.4`;
3. patch application returned exit 0;
4. read-only verification returned exit 0, `PATCHED`, at
   `0d1ffaa0c51e60b09646e9e78ff92820f375695c0dbeac59f5393e6367b43b4c`.

`settings.json` now replaces only the V1 `UserPromptSubmit` registration
with the reviewed V2 registration and adds `Stop`, `PreToolUse`, and
`PostToolUse`. The unrelated `SessionStart` entry remains. No registered
string names `nunchi-user-prompt-submit.sh`. The current settings SHA-256 is
`d612d4f27554d3ac0795b47ad511d1f96dc1b5dfb8cb589516817410eb39ee2f`.

## First live probe: defect found, no acceptance

A fresh Claude CLI session received Discord message
`1528949851285356717`. Its transcript rendered the actual envelope as
`source="plugin:discord:discord"`; the patched transport independently wrote
an owner-only native sidecar row with the same message, room, native author
`1494822530643398827` (Vigil, bot), mention, content, and timestamp.

Attempt 6 accepted only `source="discord"`, so `parse_channel_tag` returned
no channel event and the configured hook emitted the operator-prompt allow
shape. No observation state or receipts appeared. This is a live-proven
fail-open mismatch, not an inference. It caused Attempt 7 rework commit
`7ea499be33c6260f79e10f07fe77110b147929e2`.

## Successor deployment and second live probe

The installed gate was updated byte-identically from the successor:

- repository gate SHA-256:
  `c4c55671fa41caaeaa268d98ef7d74536df44b898b5d0f8ea30cf8389a53522e`;
- installed gate SHA-256: the same value;
- `cmp` result: identical.

Discord message `1528950867355635755` then traversed the live patched
transport and configured V2 hook. Durable evidence records:

- exact native event: `discord:message:1528950867355635755`;
- exact room: `discord:channel:1522258711047831653`;
- exact author: `discord:user:1494822530643398827`, kind `bot`;
- exact self mention: `discord:user:1484970897893752902`;
- request: `req-31e6d3ba-f3cc-4a60-807a-41256e77b7e4`;
- immutable observation receipt by `observation-provider`;
- immutable attention receipt by `attention-engine`, with
  `classifier_not_invoked=true`, cause `preattention-disabled`, and operator
  policy provenance;
- active wake source: `PREATTENTION_BYPASS`.

The sidecar and receipt directories and the state directory were mode `0700`.
The sidecar, room state, and both receipts were mode `0600`; `events.jsonl`
was mode `0644` inside the non-traversable `0700` state directory. This proves
reactive bot hearing, exact native identity/room binding, observation, and
trusted bypass on the installed host without overstating the leaf-file mode.

## Honest remaining boundary

The Claude CLI's account authentication had expired. After receiving the
gated wake it emitted the synthetic host error `Login expired - Please run
/login`; it did not invoke a model. Therefore this run does not fabricate a
participant outcome and does not claim a participant-host or transport
receipt. Reply, silence, privileged denial, restart recovery, and the rest of
the bounded live ladder remain pending a freshly authenticated session.
The probe session `dfe22599-986d-4f7f-8a26-59c059cd6678` was then exited
cleanly with `/exit`; the V2 transport and hook registration remain armed on
disk, and the next fresh session will exercise the documented restart reset.

Deterministic successor verification completed independently of that external
login boundary:

- `python3 -m unittest tests.v2.test_claude_code tests.test_no_home_writes tests.test_sentinel_forgery`
  — 72 tests, OK;
- `python3 -m unittest` — 1,211 tests, OK (7 skipped);
- `python3 scripts/check_governance.py --check-cli` — governance boundary and
  SpecKit 0.12.11, OK;
- `git diff --check` — clean.

Verdict: **REWORK / live-pending**, not acceptance. The transport and hook are
armed and the exact-source defect is closed; live participant completion
requires Claude re-authentication and a fresh session.
