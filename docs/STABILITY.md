# Commands and compatibility

These are the current interfaces, under [architecture review](../AGENTS.md#architecture-goal-and-current-gap).
They are not a promise that the replacement library will retain today's turn
ownership or API shapes. Document names stay stable as the library changes;
wire formats and executable interfaces retain explicit versions.

## Installed commands

| Command | Purpose |
|---|---|
| `nunchi attention`, `validate`, `probe` | Request attention, validate data, inspect the installed interfaces |
| `nunchi setup`, `config`, `diagnose`, `dashboard` | Configure and inspect the existing runtime |
| `nunchi service`, `uninstall` | Manage configured services and profiles |
| `nunchi-install` | Manage private configuration and state directories |
| `nunchi-conformance` | Run deterministic lifecycle scenarios |
| `nunchi-turn-conformance` | Check the existing turn protocol with a reference participant |
| `nunchi-channel`, `nunchi-discord`, `nunchi-matrix`, `nunchi-telegram` | Run the optional plain-model reference adapters |
| `nunchi-mcp-discord` | Run the shared Discord transport |
| `nunchi-service-worker` | Internal process used by `nunchi service` |

There are no Claude Code, Codex or Hermes integration commands or bundled
plugins. Upgrading does not uninstall an older integration from someone else's
harness configuration. Stop any old runner separately; do not point it at the
new package and expect it to work.

## Data and behavior

The [contract reference](contracts/nunchi.md) lists current interface revisions
and validation rules. In the existing implementation:

- Unknown fields are rejected. Native IDs are strings; participant identity
  comes from an authenticated actor ID, independently of names and aliases.
- Attention can return `SUPPRESS`, `WAKE` or `DEFER`. Bypass and operational
  errors are recorded separately from social judgments. A model suggesting a
  nod gives the participant a turn; Nunchi does not react on its behalf.
- Attention providers receive the same questions. OpenAI-compatible routes
  require an explicit `base_url`; there is no default provider endpoint.
- A reaction must be exactly one emoji (`I-040A@5`). Words, shortcodes and
  custom `name:id` values are rejected before dispatch.
- Continuation handles stay outside model input, are bound to one participant
  and room, expire, and are discarded on restart.
- Privileged actions require authorization for the exact operation, with
  current policy, identity, approval and replay checks.
- Missing platform capabilities are reported as limits rather than inferred.

Older receipt journals containing `ACK` records remain readable. An old `ack`
configuration setting is ignored. Executable V1 requests, commands and hooks
have been removed; old state is not migrated into new conversation turns.

Changes to a public data shape or accepted behavior need an interface-version
review, updated validation and checks of affected consumers. A library release
number alone does not identify a wire format.
