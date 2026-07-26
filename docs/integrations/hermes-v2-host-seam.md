# Hermes V2 host compatibility seam

Nunchi V2 uses a Nunchi-owned compatibility patch because the supported stock
Hermes source does not expose every host boundary required by the participant
contract. Installation does not depend on an open or unmerged Hermes pull
request, a Nunchi-maintained Hermes fork, or repository shadowing.

## Exact supported host

The wheel carries both the patch and a closed manifest under
`nunchi_hermes_v2/host_patch_assets/`. The manifest pins:

- untouched Hermes commit `243a01d5d72555061406de84890b2e9622f409cb`;
- manifest SHA-256 `243a8fa6961519d6008df81a73e16a9910d98eb0fda99d3958511937df7806cf`,
  pinned independently in installed applicator code;
- patch SHA-256 `a0dc820789c1bb7c1c1a124b00a4ddd874c7a34f4939c31b243d33cb81c11fca`;
- the closed patch operation and path set; and
- every touched path's exact pre-apply and post-apply SHA-256 and Git mode.

A different commit, divergent index, redirected Git identity environment, dirty
tracked or ignored filesystem entry, partial seam, divergent content or mode,
unsafe or symlinked root/path, wrong ownership, group/other-writable directory,
non-regular file, or corrupted asset fails closed. The verifier inventories the
complete non-`.git` filesystem rather than trusting `git status`, ignore rules,
or `core.filemode`; Git replace objects and inherited `GIT_*` redirects cannot
change the identity being checked.

## Installed workflow

Start from an untouched checkout at the supported commit and install the exact
Nunchi wheel into the operator environment. Check without mutation:

```bash
nunchi-hermes-v2-host-patch \
  --hermes-source /absolute/path/to/hermes-agent \
  --check
```

A valid untouched host reports `status: ready`. Apply transactionally:

```bash
nunchi-hermes-v2-host-patch \
  --hermes-source /absolute/path/to/hermes-agent \
  --apply
```

Success reports `status: applied`, `changed: true`, the supported commit,
manifest and patch digests, and touched-file count. Repeating either command
verifies the exact applied state and reports `changed: false`; it does not
reapply the seam.

The applicator parses the patch into a closed path/operation/mode set, proves it
matches the manifest, and materializes its result against the exact stock index
inside an isolated temporary Git repository. The host transaction is serialized
with a private lock. It re-verifies the exact HEAD, index, full filesystem
inventory, content, modes, and manifest preimages immediately before mutation;
snapshots every permitted target through descriptor-relative no-follow reads;
then installs only the isolated verified bytes through exclusive random
temporaries and descriptor-relative atomic replacement. Git never applies the
patch directly to the live host worktree.

After mutation the same independent verifier proves the complete applied state.
Any failure restores every permitted path and then proves the complete stock
state—not merely the saved files. Rollback write or verification failure is a
distinct hard failure and must never be interpreted as a clean host.

## Runtime provenance

Plugin registration re-verifies the complete applied host seam before loading
configuration or registering hooks. The public probe exposes only non-secret
cryptographic provenance: stock-host commit, patch digest, verified host-seam
digest, Nunchi integration digest, and an aggregate configuration-set digest.
It deliberately omits profile names, native room/actor/participant IDs, state
paths, and private configuration paths.

Suppression-recovery evidence binds the same verified host-seam digest. Evidence
from an older stock commit, patch, touched-file set, Nunchi integration, actor,
profile, or route cannot authorize recovery-sensitive suppression.

The seam also exposes a synchronous `gateway_shutdown` lifecycle boundary.
Hermes fires it immediately after closing gateway acceptance and before agent
draining, finalization, or adapter teardown. Nunchi invalidates every routed
runtime, pending approval, retry, delivery capability, and privileged lifecycle
generation before that callback returns.

For sends, replies, and reactions, the seam returns a closed host-owned native
acknowledgement. `sent` includes the exact platform, room, routed Hermes
profile, authenticated native self actor, effect kind, submitted content,
reply/target identity, and a new message or deterministic reaction-effect
identity. Missing or mismatched attribution is `unknown`; a bare adapter
success boolean or target message ID cannot establish success.

## Removal

Disable and uninstall the Nunchi plugin before restoring Hermes. Restore the
supported source from its exact commit with normal Git worktree operations;
do not hand-edit or reverse only part of the seam. A later Nunchi installation
must begin again from an untouched exact supported host.
