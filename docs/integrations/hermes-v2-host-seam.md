# Hermes V2 host compatibility seam

Nunchi V2 ships its required Hermes compatibility work **inside the Nunchi
wheel**. Operators do not need a Nunchi-maintained Hermes fork, an upstream
NousResearch change, or Aleph's development checkout.

The installed plugin owns three artifacts:

- a closed patch against untouched Hermes `v2026.7.20`;
- a transactional, fail-closed applicator; and
- a manifest binding the complete pre/post file identities.

This is an explicit private compatibility dependency, not a claim that Hermes
currently exposes the seam as a released public API.

## Exact supported stock host

The only supported pre-apply host is release `v2026.7.20`, commit
`3ef6bbd201263d354fd83ec55b3c306ded2eb72a`.

The wheel carries `nunchi_hermes_v2/host_patch_assets/` with:

- manifest SHA-256
  `325aacfdf0cb5ca4c2f73d09a136f934d5e264b9fbd81ca09ac8db2ea1ab4936`,
  pinned independently in applicator code;
- patch SHA-256
  `2cd45b1d8a8283d51cdb0763eb4a4964df28fb149879584a7bf29b604c5ba885`;
- 21 declared regular-file paths; and
- each path's exact operation, Git mode, and pre/post SHA-256.

A different commit, dirty or redirected Git state, undeclared filesystem entry,
partial seam, divergent mode/content, unsafe path, symlink, non-regular file,
wrong ownership, or writable ancestor fails closed.

## Install and apply

Install the exact Nunchi wheel into the same environment as the untouched
Hermes release. Check without mutation:

```bash
nunchi-hermes-v2-host-patch \
  --hermes-source /absolute/path/to/hermes-agent \
  --check
```

A valid stock host reports `status: ready`. Apply transactionally:

```bash
nunchi-hermes-v2-host-patch \
  --hermes-source /absolute/path/to/hermes-agent \
  --apply
```

Success reports `status: applied`, the exact stock commit, manifest and patch
digests, touched-file count, and whether bytes changed. Repeating either command
verifies the exact applied state and is idempotent.

The applicator never asks Git to patch the live worktree. It first parses the
patch into a closed path/operation/mode set, verifies the complete stock
inventory and literal commit, and materializes the candidate in an isolated
temporary Git repository. It then snapshots every permitted path, performs
no-follow descriptor-relative atomic replacements, and verifies the complete
post-state. Any failure restores and re-verifies the complete stock state;
rollback failure is a distinct hard failure.

## Runtime contract

After application, Hermes exposes gateway-message hook API version 2. Nunchi is
still installed through the ordinary `hermes_agent.plugins` entry point. The
seam provides:

- post-control, post-authorization ordinary-message handling on cold and busy
  ingress;
- immutable event and route snapshots;
- callback-scoped, one-shot route-bound send, reply, and reaction operations;
- per-native adjudication of coalesced batches, with mixed batches reduced to
  only their pass-through events before ordinary dispatch;
- adapter-produced native delivery acknowledgement;
- explicit session-cancel and awaited gateway-shutdown lifecycle boundaries;
- replay/startup exclusion and deterministic hook-conflict rejection.

The route-bound delivery object is a supported-use facade for trusted
in-process plugins, not a hostile-Python sandbox. It exposes no adapter or
native client through its API.

Revocation synchronously prevents any new native invocation. An invocation that
already started is not cancelled merely to manufacture failure: the lifecycle
boundary waits for its adapter callback to settle, and the public receipt is
`unknown` if revocation won while it was in flight. An unsuccessful adapter
result is also `unknown`: timeout, partial chunk delivery, and post-submission
failure cannot prove non-occurrence. `failed` is reserved for host-side
pre-invocation fences. A plugin or adapter that spawns untracked external work
and returns early violates the in-process host contract.

Discord fallback from a native reply attempt to an unthreaded send is attested
as a send, never as a reply. `gateway_message` and the legacy behavior-changing
`pre_gateway_dispatch` hook are mutually exclusive; discovery rejects the
configuration regardless of plugin load order rather than dropping live
messages according to order.

## Provenance and removal

Plugin registration verifies the exact applied seam before loading Nunchi
configuration or registering hooks. Public probes expose non-secret
cryptographic provenance: stock commit, patch digest, verified seam digest,
Nunchi integration digest, and aggregate configuration digest.

To remove the seam, first disable/uninstall Nunchi, then restore Hermes from the
exact stock commit with normal Git worktree operations. Do not hand-reverse a
subset. A later installation starts again from untouched `v2026.7.20`.
