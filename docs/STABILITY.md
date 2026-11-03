# Commands

These commands come from the code under
[architecture review](../AGENTS.md#architecture-goal). None
of them is a compatibility promise for the replacement library.

| Command | Purpose |
|---|---|
| `nunchi attention`, `validate`, `probe` | Request attention, validate data, inspect the installed interfaces |
| `nunchi setup`, `config`, `diagnose`, `dashboard` | Configure and inspect the existing runtime |
| `nunchi service`, `uninstall` | Manage configured services and profiles |
| `nunchi-install` | Manage private configuration and state directories |
| `nunchi-conformance` | Run deterministic lifecycle scenarios (obsolete) |
| `nunchi-turn-conformance` | Check the existing turn protocol (obsolete) |
| `nunchi-channel`, `nunchi-discord`, `nunchi-matrix`, `nunchi-telegram` | Run the plain-model reference adapters (obsolete) |
| `nunchi-mcp-discord` | Run the shared Discord transport |
| `nunchi-service-worker` | Internal process used by `nunchi service` |

There are no Claude Code, Codex or Hermes integration commands or bundled
plugins.

The [contract reference](contracts/nunchi.md) lists current interface
revisions and validation rules.
