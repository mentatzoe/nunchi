# Archived Hermes Nunchi V1 surface

This note records the retired integration shape for migration history only. It is
not loaded by the Hermes plugin and is not a supported product path.

The V1 plugin used a subprocess admission gate, per-channel mutable settings,
and a `/nunchi` administrative command. Its output contract exposed
`PASS / ACK / ASK / SPEAK` verdicts and patched several host emitters for a
quiet-room mode. Those mechanisms were removed at the V2 cutover because they
mixed admission with participant output, relied on text verdicts, and left a
second callable gate/command path beside the stateful V2 lifecycle.

V2 keeps only the native-event boundary, structured observation and attention,
one exact redispatch ticket, a normal act-or-silence Hermes participant turn,
canonical effect authorization, and ordered participant/transport receipts.
Operators must use the top-level `nunchi:` V2 configuration documented in
`integrations/hermes/README.md`; no V1 command or verdict compatibility alias is
provided.
