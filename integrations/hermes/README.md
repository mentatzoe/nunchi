# Hermes integration — Nunchi V2

`nunchi-v2` is a wheel-distributed Hermes plugin. The complete compatibility
implementation travels in the Nunchi artifact: operators do not depend on an
upstream NousResearch change, a Nunchi-maintained Hermes fork, or a developer's
pre-patched checkout.

## Supported host

The current artifact supports untouched Hermes `v2026.7.20`, exact commit
`3ef6bbd201263d354fd83ec55b3c306ded2eb72a`. Stock Hermes does not expose the
required participant boundary, so the wheel includes a closed, exact-version
compatibility patch and transactional applicator.

Check and apply it with:

```bash
nunchi-hermes-v2-host-patch \
  --hermes-source /absolute/path/to/hermes-agent \
  --check

nunchi-hermes-v2-host-patch \
  --hermes-source /absolute/path/to/hermes-agent \
  --apply
```

The first command accepts only the complete untouched stock identity. The
second materializes the reviewed result in isolation, atomically applies the
closed path set, verifies every post-image, and rolls back on failure. Repeated
application is verification-only and idempotent.

The canonical manifest, patch bytes, applicator, package-data declaration, and
adversarial tests all live in this repository and wheel. See
[`docs/integrations/hermes-v2-host-seam.md`](../../docs/integrations/hermes-v2-host-seam.md)
for exact digests and safety semantics.

## Configure the plugin

After the exact seam is verified, generate one closed profile-bound config:

```bash
nunchi-hermes-v2-config \
  --hermes-profile default \
  --platform discord \
  --room-id 1234567890 \
  --actor-id discord:actor:1234 \
  --participant-id aleph \
  --profile-id aleph \
  --instructions-file /absolute/path/to/participant-instructions.md \
  --output-dir /absolute/private/config \
  --state-root /absolute/private/state \
  --provenance trusted:operator-config
```

Hermes discovers the `nunchi-v2` entry point normally. Adapter-local profile
names map to the shared platform-neutral opaque identity
`installation_id="hermes:<profile>"`.

## Commissioning boundary

Source tests and successful patch application are not live commissioning. No
repository checkout or editable install counts as clean artifact evidence.
Before claiming a deployed room works, the exact wheel + stock commit + patch
manifest + config must pass clean-install discovery, deterministic lifecycle
and receipt tests, independent exact-byte review, and separately authorized
native Discord/Telegram canaries.
