# Nunchi V2 compatibility and stability

V2 is a breaking, atomic product contract. The installed command set is frozen
in [`product-surface-v2.md`](product-surface-v2.md); every retained command must
implement V2 and every removed V1 command must remain absent. There is no hidden
`nunchi admit`, PASS/ACK/ASK/SPEAK Python API, legacy channel sentinel, Codex
prompt/send gate, or V1 room runner.

Portable schema versions, closed fields, request correlation, exact identity,
continuation secrecy, receipt ownership, and authorization semantics are
defined under [`../schemas/v2/`](../schemas/v2/) and
[`architecture/v2-selected-design.md`](architecture/v2-selected-design.md).
Additive changes require explicit schema/version treatment; weakening exact
identity, provenance, single-attestation, freshness, or authorization is not a
compatible change.

The published `0.2.0` V1 behavior remains reproducible from release history and
the explicitly labeled documents under [`archive/v1/`](archive/v1/). The
unaccepted Hermes and Claude Code packet directories also still contain
prominently labeled inherited V1 input, but `nunchi-install` refuses to copy or
register it. Historical contracts and evidence are not callable compatibility
paths in the V2 wheel. The frozen candidate cannot be declared free of all V1
integration code until accepted V2 packets replace those two directories.

The candidate is not a release merely because these contracts exist. Release
requires the clean installed provenance probe, deterministic and live parity,
accepted platform packets, frozen-candidate cross-family review, blocker fixes,
successor re-review, and exact-main post-merge verification described in
[`evaluations/v2.md`](evaluations/v2.md).

Packaging uses a fresh build-library directory for every wheel so a deleted
module cannot survive from an earlier local build. The installed-provenance
probe also compares the wheel's complete `nunchi/` file inventory with
`src/nunchi/`; metadata and entry-point checks alone are insufficient.
