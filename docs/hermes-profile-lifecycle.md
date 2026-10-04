# Reversible Hermes profile lifecycle

The installed `nunchi-hermes-lifecycle` command plans and applies a stopped,
profile-local cutover. It never installs packages, signals a process or claims
that a running process adopted new code. Its `plan`, `apply`, `verify` and
`rollback` results use JSON schema version 1.

This procedure covers fresh V2 activation, the historical V1 installer tree
`dd03add96128d2658deff2201d7a566722cd5603`, and retirement/restoration of an
attributed V2 profile. It does not convert V1 social policy or history. Modified
or unknown predecessors require ownership reconciliation; do not rename or
remove them just to bypass the refusal. Only historical file identities ship in
V2, not a V1 compatibility runtime.

## Select and retain before changing anything

Use the actual Hermes environment's absolute Python path, not whichever Python
happens to be on PATH. All commands below use that interpreter. Keep the exact
reviewed candidate wheel and the exact predecessor wheel in a private operator
archive. A version string alone is not artifact identity. The command checks
installed RECORD entries and wheel identity, including uv's local-wheel
provenance, and refuses an editable/source-only install. Retain the wheel at its
installation path while planning/applying: local-wheel provenance is compared
to its installed contents.

Stop the affected gateway, CLI workers and dashboards using existing operator
service controls. Keep them stopped until profile AND package operations have
finished. `--processes-stopped` records your assertion; it is not process
inspection and is not permission for the command to restart anything.

A package environment can serve multiple profiles, including profiles outside
the selected home. Every plan reports this shared scope and records the selected
interpreter/prefix; it cannot exhaustively enumerate those consumers. Inventory
and stop them before installing a different wheel. If another profile must keep
its existing package, do not replace that shared environment: select a separate
Hermes environment instead. The lifecycle itself changes only the selected
profile. It never silently upgrades or uninstalls the shared package.

Use absolute paths in these examples; substitute your actual values:

```sh
umask 077
HERMES_PYTHON=/absolute/hermes/.venv/bin/python
HERMES_HOME=/absolute/selected/profile
PROFILE=default
WHEEL=/private/artifacts/nunchi-2.0.0-py3-none-any.whl
OLD_WHEEL=/private/artifacts/nunchi-0.2.0-py3-none-any.whl
CONFIG=/private/artifacts/new-v2-config.json
export HERMES_HOME
uv pip install --python "$HERMES_PYTHON" --no-deps --reinstall "$WHEEL"
shasum -a 256 "$WHEEL" "$OLD_WHEEL" "$CONFIG"
```

Nunchi has no mandatory package dependencies; it uses the selected stock Hermes
environment's dependencies: modern Hermes provides `hermes_yaml` plus ruamel
(load/dump and token/node parsing); releases 0.19.0/0.21.5 provide PyYAML.
A broken modern host parser is an error, not permission to fall back. No extra
parser installation is needed on these stock hosts. Do not install the source
`[test]` extra into a modern host proof environment: that extra declares PyYAML
for the no-Hermes offline suite only.
Minimum stock's uv environment need not contain pip.
If using pip, first run `"$HERMES_PYTHON" -m pip --version`; only if available use
`"$HERMES_PYTHON" -m pip install --no-deps --force-reinstall "$WHEEL"` instead.
Do not install pip into an unrelated interpreter as a workaround.

The candidate config must pass the existing pinned V2 validation and name this
exact profile. Its `state_directory` must equal
`default_config_paths(PROFILE, hermes_home=Path(HERMES_HOME)).state_directory`
from `nunchi.integrations.hermes_dashboard_store`: the directory is
`HERMES_HOME/nunchi/profiles/<profile-storage-key>/state`, where the storage key
includes a digest of the exact profile name. Obtain it from that API rather
than inventing a directory. Author new V2 bindings using the integration
README; do not reinterpret a V1 state file. Keep file-backed participant
snapshots available at their pinned paths if used. Existing V2 data must be
retired first, rather than overwritten by activation.

Runtime config overrides (`NUNCHI_HERMES_V2_CONFIG*`, including assignments in
the profile `.env`) and project plugin discovery must be reconciled and unset
before using this profile-local procedure. It refuses these redirects rather
than applying to a different effective configuration. It reads no secret values
into output. Do not publish the private config, backup files or state.

## Plan, inspect, then apply

Enter the hashes from the previous command and keep your working directory
outside any source checkout. For a fresh profile omit `--predecessor-wheel`.
For an attributed V1 cutover it is required.

```sh
WHEEL_SHA256=the_reviewed_wheel_sha256
CONFIG_SHA256=the_supplied_config_sha256
"$HERMES_PYTHON" -I -m nunchi.integrations.hermes_lifecycle plan \
  --hermes-python "$HERMES_PYTHON" --hermes-home "$HERMES_HOME" \
  --mode activate --profile "$PROFILE" --wheel-sha256 "$WHEEL_SHA256" \
  --config "$CONFIG" --config-sha256 "$CONFIG_SHA256" \
  --predecessor-wheel "$OLD_WHEEL" > activation-plan.json
```

Planning is read-only. Inspect the returned resolved home, interpreter, package
identity, predecessor identity, operations and `plan_sha256`. Plans contain
paths and hashes, not config/state values. Do not approve a plan for the wrong
profile. A validated selected-home alias is allowed; descendant symlinks,
hard-linked files, unknown ownership and changed inputs are refused. Host YAML
anchors/aliases, duplicate mapping keys and general flow-style YAML mappings are
refused rather than risk rewriting private configuration incorrectly. Strict
JSON objects, including existing and new dashboard Saves, are supported directly:
only plugin activation-list values are spliced, preserving unrelated bytes,
including attention trust entries. No manual conversion or restart is needed.
Non-JSON flow syntax, duplicate JSON keys and non-finite JSON constants are refused.
Explicit YAML document start/end markers are retained. The rendered document is
parsed again with the host parser and compared
with the intended mapping during planning, before it can be staged or published;
unsupported layouts are refused read-only.

```sh
PLAN_SHA256=the_inspected_plan_sha256
"$HERMES_PYTHON" -I -m nunchi.integrations.hermes_lifecycle apply \
  --hermes-python "$HERMES_PYTHON" --hermes-home "$HERMES_HOME" \
  --plan activation-plan.json --plan-sha256 "$PLAN_SHA256" \
  --processes-stopped > activation-receipt.json
```

Apply revalidates the complete plan, locks this home, stages private new files,
journals the transaction and renames each before-image into
`HERMES_HOME/.nunchi-lifecycle/TRANSACTION/` before replacing its target. That
0700 archive is outside plugin discovery; its files are private. Historical
runtime copies and historical backup copies under `plugins` are quarantined,
never left as a second executable fallback. Known V1 state/log files move there
without translation. Custom/out-of-home predecessor state paths are refused.
Historical V1 defaults use `~/.hermes`, not `HERMES_HOME`: missing, null, empty,
false or zero `state_path` values fall back there. Only `log_path` supports
null/empty/false/zero/no/off/none as disabled values. A named-profile V1 install
with machine-home defaults therefore needs explicit operator reconciliation;
the command does not inspect or archive that machine state on its behalf.
Unrelated files and host config/trust outside the plugin activation node retain
their bytes. The complete original config is retained privately for guarded
restoration. No command purges archives.

The activation marker opts this profile into profile-only dashboard startup.
Startup verifies its already-staged bridge instead of installing/enabling
Nunchi in the machine profile. Use the profile's isolated dashboard, or provision
a shared machine dashboard separately and explicitly. Older ordinary installs
may have separately enabled a machine profile; this transaction does not
silently retire that other profile.

```sh
TRANSACTION=the_transaction_from_activation_receipt
"$HERMES_PYTHON" -I -m nunchi.integrations.hermes_lifecycle verify \
  --hermes-python "$HERMES_PYTHON" --hermes-home "$HERMES_HOME" \
  --transaction "$TRANSACTION"
```

Verification is repeatable while stopped. `running_process_adoption: false`
is intentional: filesystem verification does not prove live adoption. Restart
through existing service controls; fresh discovery must show one enabled
`nunchi` successor and no discoverable `nunchi-gate`, then run `/nunchi probe`
and the existing authorised canaries. Normal runtime writes change managed
state, so an old transaction's exact verification/rollback may then refuse.
Installed local tests are not a live platform acceptance claim.

## Return to stock and optionally remove the package

Stop the selected processes again. Plan retirement with the same candidate
wheel still installed:

```sh
"$HERMES_PYTHON" -I -m nunchi.integrations.hermes_lifecycle plan \
  --hermes-python "$HERMES_PYTHON" --hermes-home "$HERMES_HOME" \
  --mode retire --profile "$PROFILE" --wheel-sha256 "$WHEEL_SHA256" \
  > retirement-plan.json
```

Inspect its new `plan_sha256`, apply with `--plan retirement-plan.json` and
`--processes-stopped`, then verify its new transaction as above. Retirement
archives owned dashboard/config/state, removes the lifecycle activation marker,
and disables both Nunchi runtime names. It preserves unrelated user data and
attention trust. Unknown files or edited dashboard assets are not silently
archived. Fresh stock discovery must have no enabled Nunchi runtime.

You can leave the package installed for other consumers. Only after every
consumer of this interpreter has been retired/stopped may you remove it:

```sh
uv pip uninstall --python "$HERMES_PYTHON" nunchi
# Or, only with pip verified in that same interpreter:
# "$HERMES_PYTHON" -m pip uninstall nunchi
```

Package uninstall does not erase private transaction archives. Reinstall the
exact V2 lifecycle wheel before invoking a retired profile's restore command.
The shared `nunchi uninstall` command is not this profile cleanup mechanism.

## Guarded restoration and interrupted transactions

While affected processes remain stopped, restore using the recorded transaction
and its ORIGINAL plan digest, not a newly manufactured plan:

```sh
"$HERMES_PYTHON" -I -m nunchi.integrations.hermes_lifecycle rollback \
  --hermes-python "$HERMES_PYTHON" --hermes-home "$HERMES_HOME" \
  --mode restore --transaction "$TRANSACTION" \
  --plan-sha256 "$PLAN_SHA256" --processes-stopped
```

All targets are checked before restoration starts and again at each move.
Publication uses the kernel's atomic no-replace rename on macOS/Linux; an
unsupported kernel/filesystem refuses rather than emulating it with a racy
existence check. The lifecycle lock does not coordinate external editors.
A destination appearing during apply/restore is left intact. A source changed
in the check-to-move interval is captured in the archive and causes refusal,
not replacement by another version; the target can then be absent. Keep
processes stopped and preserve all before-images, captured conflicts and the
receipt for operator reconciliation. Do not resume a partial transaction by
removing conflicting files or editing its journal.

If any target has later edits or the home/parent identity changed, the command
refuses instead of clobbering it. There is no force flag. Preserve those files
and the receipt for operator reconciliation; do not delete journals, rewrite receipts or reset
state to bypass the check. An ordinary apply failure restores its managed
before-state automatically when safe. After an abrupt exit, `verify` reports
an interrupted transaction and a new apply is blocked until stopped rollback
recovers it. Read its transaction ID from the private store and its digest from
the retained plan. A crash in the narrow interval between creating a parent
and recording its identity deliberately requires operator reconciliation;
it will not delete an unrecorded directory.

Restoring retirement reinstates the exact pre-retirement V2 state. Restoring
activation reinstates its predecessor filesystem state, but does NOT install
its package. For a V1 return, first finish guarded restoration while the V2
lifecycle command is available, verify it, then install the retained old wheel
from the transaction (its original valid wheel filename is preserved):

```sh
uv pip install --python "$HERMES_PYTHON" --no-deps --reinstall \
  "$HERMES_HOME/.nunchi-lifecycle/$TRANSACTION/predecessor-package/nunchi-0.2.0-py3-none-any.whl"
```

Check that wheel's hash against `predecessor_package.sha256` in the receipt
before installing. Keep all affected consumers stopped throughout the package
change. Only an explicitly requested stopped rollback may return V1; it never
runs as a hidden fallback. Restart and check fresh discovery against the
recorded predecessor. Previously issued native effects cannot be undone.

## Reproducible verification scope

`tests/v2/test_hermes_lifecycle.py` exercises dry planning, privacy, activation,
retirement, every commit checkpoint failure, alias/path redirection, ownership,
lock contention, drift, receipt binding and real child-process hard exit.
`tests/v2/lifecycle_installed_probe.py` is a disposable tests-only runner: supply
`--uv`, `--old-wheel`, `--new-wheel`, `--legacy-source`, and run it with the
selected stock Hermes Python outside the source checkout. HOME must be a
private child of that working directory. It deliberately installs/removes
Nunchi in that disposable interpreter. It tests actual historical installation,
cutover, one successor registration, profile plus archived-wheel restoration,
real dashboard Save followed by retirement and verification, package removal/
reinstallation, byte-exact guarded restoration and reactivation. The Save cycle
runs for default and named profiles, preserving attention trust and unrelated
machine/sibling config. It compares host sources and other distributions' RECORD
files. Never run that
probe in a live Hermes environment.

The reviewed normal-turn, attention, startup and contract checks remain
required in addition to lifecycle tests. This feature does not close unrelated
surface/live acceptance gaps or claim any running gateway adoption.
