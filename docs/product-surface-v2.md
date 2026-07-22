# Nunchi V2 installed product surface

> Candidate contract. V1 remains the verified current product until the atomic
> V2 candidate is accepted, merged, and verified on `main`.

“Every entry point is V2 or deliberately removed” means the installed wheel has
one closed console-script set. A useful surface is migrated; it is not removed
merely because migration is inconvenient. Only a behavior that is superseded
or forbidden by the selected V2 lifecycle is removed.

| Installed command | Final decision | Required V2 behavior |
|---|---|---|
| `nunchi` | Keep and migrate | V2 request/decision CLI only; no `admit` or V1 verdict branch |
| `nunchi-install` | Keep and migrate | Install and verify the accepted Hermes and Claude Code V2 packets plus shared V2 CLI; no V1 hook/plugin artifacts |
| `nunchi-channel` | Keep and migrate | Generic exact-host binding through shared observation, attention, freshness, participant and receipt lifecycle |
| `nunchi-discord` | Keep and migrate | Standalone Discord V2 lifecycle with exact snowflakes and honest capabilities |
| `nunchi-matrix` | Keep and migrate | Matrix V2 lifecycle with native MXIDs, relations, membership and honest restart limits |
| `nunchi-telegram` | Keep and migrate | Telegram V2 lifecycle with numeric identity, structured mentions and honest history/reaction gaps |
| `nunchi-mcp-discord` | Keep and migrate | Shared Discord V2 source/action transport as the sole default; no opt-in V1 mode |
| `nunchi-codex-room-v2` | Keep | Direct, persistent, tool-empty Codex participant over the shared V2 runtime |
| `nunchi-codex-config-app` | Keep and migrate | Configure only trusted V2 policy/identity/runtime state and never expose secrets to room content |

The final wheel deliberately omits exactly these superseded commands:

| Removed command | Why removal preserves rather than drops the product requirement |
|---|---|
| `nunchi-codex-prompt-gate` | The accepted Claude Code V2 packet owns its native wake integration; the V1 hook is not retained as a compatibility path. |
| `nunchi-codex-send-gate` | V2 forbids send-time social reclassification. Operational send safety remains in transport backstops. |
| `nunchi-codex-room-runner` | The old PASS/ACK/ASK/SPEAK room runner is replaced by `nunchi-codex-room-v2`, not by loss of Codex room presence. |

V1 Python runtime symbols and commands are removed from the shipped package as
part of the same breaking cutover. Historical documents, tests and evidence may
name V1 when explicitly labeled historical; importable product code may not
offer a hidden V1 path.

## Reproducible audit

```sh
python3 -m evals.v2.provenance.runner --deterministic-time
python3 -m evals.v2.provenance.runner \
  --install \
  --output evidence/v2/provenance/installed-<run-id>.json
```

The repository audit compares `pyproject.toml` to the closed surface table,
requires a V2 major version, and groups exact V1 residue by file and symbol
across both the importable package and ordinary integration runtime sources.
Historical docs, tests, and evidence are outside that runtime scan. The install
probe builds a wheel offline, records its SHA-256 digest,
creates a fresh virtual environment, installs without dependency or index
resolution, reads installed distribution metadata in isolated Python mode, and
runs every required command's `--help` path under a minimal environment. Help
must be import-safe and must not require a platform token, network, or optional
runtime dependency.

The probe records the source commit and dirty state that produced the wheel.
It never treats a source-tree import, an editable install, or a matching version
string as installed provenance. Output uses exclusive creation and never
overwrites older evidence. Any unexpected console script fails the audit even
if it was not previously known as V1; this prevents an unreviewed side door.
