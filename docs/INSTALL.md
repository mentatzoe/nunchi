# Installing Nunchi's operator artifacts (`nunchi-install`)

Nunchi ships integration artifacts that must live in **stable operator
locations**, decoupled from any git checkout:

| Artifact | Source (in the repo) | Installed to |
|----------|----------------------|--------------|
| Hermes gateway plugin | `integrations/hermes/nunchi-gate/` | `$HERMES_HOME/plugins/nunchi-gate/` (default `~/.hermes`) |
| Claude Code hooks | `integrations/claude-code/nunchi_gate_hook.py`, `nunchi_prompt_gate.py` | `~/.claude/hooks/` (+ two shell wrappers) |
| `nunchi-channel` CLI | the `nunchi` package | your `PATH` (via `pip install nunchi`) |

`nunchi-install` installs the first two groups by **copying** — never
symlinking — and stamps each destination with the source commit it was built
from. It checks that `nunchi-channel` is on `PATH` (it does not install it).

## Why we copy, not symlink

This installer exists because of a real incident.

- **The Hermes plugin was symlinked** from `~/.hermes/plugins/nunchi-gate`
  into a live git checkout. Hermes ran whatever the symlink pointed at. When
  the checkout **switched branches**, the running plugin silently became that
  branch's code — a stale, unintended plugin, with no signal to the operator.
  A gate that reads the room is worthless if a `git checkout` elsewhere on the
  machine quietly swaps it for last week's logic.
- **The Claude Code hooks were registered by floating checkout paths**
  (`/Volumes/.../integrations/claude-code/...`) directly in `settings.json`.
  When that path moved or the volume unmounted, the hooks broke.

The fix is to **copy** each artifact into a stable, checkout-independent
location, and to point `settings.json` at **stable wrapper paths** under
`~/.claude/hooks/` rather than at a repo. A branch switch in the checkout can
no longer change the running plugin; upgrades are explicit (`nunchi-install
upgrade`) and leave a version stamp you can audit with `nunchi-install
verify`. If a symlinked destination is found, it is detected, its target
recorded, backed up, and replaced with a real copy.

## Prerequisites

`nunchi-install` copies **from a checkout** (the `integrations/` tree is not
part of the published wheel). Install the package for the CLI, then run
`nunchi-install` from inside a checkout — or point it at one with
`--repo-root`:

```sh
pip install nunchi          # provides nunchi-channel + the nunchi-install script
git clone https://github.com/mentatzoe/nunchi && cd nunchi
nunchi-install install      # source auto-discovered from the current checkout
```

From a source tree without installing:

```sh
PYTHONPATH=src python3 -m nunchi.install install
```

## Commands

### `install`

Copies all three artifact groups. Any existing copy is backed up (timestamped
`.bak`) before being overwritten; a symlinked destination is replaced with a
real copy (see below). Prints the `settings.json` snippet at the end.

```sh
nunchi-install install
```

### `upgrade`

Re-copies **only** the artifacts whose source commit differs from the
installed stamp (or that are missing / symlinked). Backs up the old copy
first. In-sync artifacts are skipped. Use `--force` to re-copy regardless.

```sh
nunchi-install upgrade
nunchi-install upgrade --force
```

### `verify`

Reports installed-vs-repo drift per artifact, one of:

- `in-sync` — installed stamp matches the current source commit;
- `stale` — installed, but from a different commit (or unmanaged/no stamp);
- `not-installed` — nothing installed;
- `symlink-found` — the destination is a symlink (the exact bug this tool
  fixes) — run `install`/`upgrade` to replace it with a real copy.

```sh
nunchi-install verify
```

### `uninstall`

Removes the installed copies. If `install` had replaced a symlink, the
original symlink is restored. Operator files the installer did not create
(e.g. your own notes in `~/.claude/hooks/`, and any `.bak` backups) are left
untouched.

```sh
nunchi-install uninstall
```

### `print-claude-settings`

Prints just the `settings.json` hook registration snippet (see below).

```sh
nunchi-install print-claude-settings
nunchi-install print-claude-settings --matcher '.*__reply$'
```

## Global flags

| Flag | Effect |
|------|--------|
| `--dry-run` | Print every planned action; touch nothing on disk. |
| `--prefix DIR` | Base dir; homes default to `DIR/.hermes` and `DIR/.claude`. |
| `--hermes-home DIR` | Hermes home (default `$HERMES_HOME` or `~/.hermes`). |
| `--claude-home DIR` | Claude Code home (default `~/.claude`). |
| `--repo-root DIR` | Source checkout to copy from (default: auto-discovered). |
| `--only GROUP` | Limit to `hermes`, `claude`, and/or `cli` (repeatable). |

Flags work before or after the subcommand: `nunchi-install --dry-run install`
and `nunchi-install install --dry-run` are equivalent.

## Registering the Claude Code hooks in `settings.json`

`nunchi-install` **does not edit `settings.json`** — that file is yours. After
an install it prints the exact block to merge (regenerate any time with
`nunchi-install print-claude-settings`). The commands point at the **stable
wrapper paths**, never a repo checkout:

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "~/.claude/hooks/nunchi-user-prompt-submit.sh",
            "timeout": 35
          }
        ]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "mcp__plugin_discord_discord__reply",
        "hooks": [
          {
            "type": "command",
            "command": "~/.claude/hooks/nunchi-pretool-reply.sh",
            "timeout": 35
          }
        ]
      }
    ]
  }
}
```

(The printed snippet uses your resolved absolute `~/.claude` path.) Restart or
reload the Claude Code session for `settings.json` changes to take effect.

### The wrappers are fail-open

Each wrapper (`nunchi-pretool-reply.sh`, `nunchi-user-prompt-submit.sh`)
sources an optional operator env file (`~/.claude/nunchi-gate.env`), then runs
the Python hook. **Any** failure — a missing hook file, no `python3`, a hook
error — exits `0`, so a missing or broken gate can never block Claude Code.
Put your `NUNCHI_HOOK_*` and classifier environment variables in
`~/.claude/nunchi-gate.env` (it is sourced if present; the installer never
overwrites it).

## Version stamps

Each destination gets a `.nunchi-install.json` marker recording the source
commit (`git rev-parse HEAD`, falling back to a `VERSION` file or `"unknown"`),
the source path, the install timestamp, and the files copied. `verify` and
`upgrade` read it to detect drift. A replaced symlink also records its old
target and backup path there.

## What is still manual

`nunchi-install` is honest about its scope. It does **not**:

- edit `settings.json` (it prints the snippet; you merge it);
- install `nunchi-channel` (run `pip install nunchi`);
- configure the classifier env (`NUNCHI_CLASSIFIER_MODEL`, `OPENROUTER_API_KEY`
  — see [`integration.md`](integration.md));
- enable the Hermes plugin (`plugins.enabled` / the `nunchi:` block in
  `~/.hermes/config.yaml`) or set `DISCORD_ALLOW_BOTS` — see the
  [Hermes README](../integrations/hermes/README.md);
- apply the operator-carried Hermes core-patch or the Claude Code
  transport-patch (separate, documented manual steps).
