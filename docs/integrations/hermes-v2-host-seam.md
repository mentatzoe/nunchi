# Hermes V2 host compatibility seam

Nunchi V2 uses a Nunchi-owned compatibility patch because the supported stock
Hermes source does not expose every host boundary required by the participant
contract. Installation does not depend on an open or unmerged Hermes pull
request, a Nunchi-maintained Hermes fork, or repository shadowing.

## Exact supported host

The wheel carries both the patch and a closed manifest under
`nunchi_hermes_v2/host_patch_assets/`. The manifest pins:

- untouched Hermes commit `243a01d5d72555061406de84890b2e9622f409cb`;
- patch SHA-256 `d3135254b3eea1237db8bfb0e597a5a74e20c26edaa02d8b57d5e6a1d6fdaa42`;
- every touched path and its exact post-apply SHA-256 identity.

A different commit, dirty tree, partial seam, divergent file, unsafe path,
non-regular file, or corrupted asset fails closed.

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

Success reports `status: applied`, `changed: true`, the supported commit, patch
digest, and touched-file count. Repeating either command verifies the exact
applied state and reports `changed: false`; it does not reapply the seam.

Application snapshots every touched path, uses `git apply` only after exact
source and patch checks, and verifies all resulting digests plus the complete
changed-path set. Any failed post-apply verification restores the snapshots.
Rollback failure is reported as a distinct hard failure and must never be
interpreted as a clean host.

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

## Removal

Disable and uninstall the Nunchi plugin before restoring Hermes. Restore the
supported source from its exact commit with normal Git worktree operations;
do not hand-edit or reverse only part of the seam. A later Nunchi installation
must begin again from an untouched exact supported host.
