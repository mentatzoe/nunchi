# Codex V2 integration

Codex participates directly through `nunchi-codex-room-v2`. The inherited
prompt hook, send hook, PASS/ACK/ASK/SPEAK room runner, and plugin bundle are
deliberately absent: V2 judges pre-attention once, wakes a tool-empty
participant with a fresh current room tail, and sends a structured action or
nothing through the shared transport.

## Components

| Component | Responsibility |
|---|---|
| `nunchi-mcp-discord` | Exact Discord facts and allowlisted actions behind separate bearer authentication |
| `nunchi-codex-room-v2` | Backfill-as-context, one-active/one-newest-pending scheduling, attention, persistent Codex turn, and receipts |
| `nunchi-codex-config-app` | Secret-redacted policy/session/receipt inspection and explicitly enabled non-secret control changes |

The Codex participant has a dedicated owner-only `CODEX_HOME` and empty
workspace. Its invocation disables shell, web, apps, plugins, skills, MCP, code
mode, multi-agent, and permission tools; ignores ambient instructions; inherits
no operator environment; and rejects any observed tool event or unknown JSONL
shape. The persistent thread advances only after both the completed Codex event
lifecycle and the strict structured action artifact validate. It returns only a
message action, reaction action, or `null`.

## Run

Prepare the owner-only policy, receipt directory, Codex home, empty workspace,
and session directory as described in
[`../../docs/operators/v2.md`](../../docs/operators/v2.md). Start the
authenticated Discord source, then:

```sh
export NUNCHI_MCP_DISCORD_AUTH_TOKEN='<separate random bearer secret>'
nunchi-codex-room-v2 \
  --policy /absolute/path/to/nunchi-policy.json \
  --channel-id 123456789012345678 \
  --self-user-id 987654321098765432 \
  --participant-id vigil \
  --participant-name Vigil \
  --session-path /absolute/owner-state/codex-session.json \
  --codex-home /absolute/owner-state/codex-home \
  --participant-workspace /absolute/owner-state/empty-workspace
```

The transport bearer is read from `NUNCHI_MCP_DISCORD_AUTH_TOKEN` by default;
`--transport-auth-env` accepts an environment-variable name, never a secret
argument. HTTP is loopback-only and remote transports require HTTPS. Redirects
must remain on the exact original origin.

## Configuration app

The app is read-only by default:

```sh
nunchi-codex-config-app \
  --policy /absolute/path/to/nunchi-policy.json \
  --session /absolute/owner-state/codex-session.json
```

`--allow-policy-write` explicitly enables app-only optimistic writes to exactly
four non-secret controls: pre-attention enablement, social suppression
enablement, provider-error action, and the transition DEFER margin. Every write
must present the exact policy provenance that was inspected. Identity, grants,
provider endpoint/model/credential, budgets, receipt destination, and
recoverability cannot be changed through the app. `--allow-session-reset`
separately enables removal of the persistent thread binding. Neither authority
is inferred from room content.

See [`../../docs/integrations/codex-v2.md`](../../docs/integrations/codex-v2.md)
for the sequence and security boundary.
