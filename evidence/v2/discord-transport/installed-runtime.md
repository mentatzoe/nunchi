# Discord V2 installed-runtime evidence

**Source commit:** `c95ea79e952bcf7803b54d24ba84485ba9ff0804`

**Evidence grade:** clean local wheel install plus exact SDK-bound deterministic
execution. This is not a live Discord-room claim.

The candidate was built and installed non-editably into the new virtual
environment `/private/tmp/nunchi-v2-050-epoch.Dep6vs`:

```text
Python 3.14.3
nunchi=0.2.0
mcp=1.28.1
nunchi_path=/private/tmp/nunchi-v2-050-epoch.Dep6vs/lib/python3.14/site-packages/nunchi/__init__.py
wheel_sha256=556e3022590b5977bf8de0632b50c97a33e55936cf35e51333d3c16fc8ea90a9
```

Commands:

```sh
python3 -m venv /private/tmp/nunchi-v2-050-epoch.Dep6vs
/private/tmp/nunchi-v2-050-epoch.Dep6vs/bin/python -m pip install \
  --disable-pip-version-check '.[mcp-discord]'
PYTHONDONTWRITEBYTECODE=1 \
  /private/tmp/nunchi-v2-050-epoch.Dep6vs/bin/python -m unittest -v \
  tests.test_mcp_discord_server \
  tests.v2.test_discord_transport \
  tests.test_mcp_discord_gateway \
  tests.v2.test_mcp_transport_client_v2
```

Result: `141` passed, `1` skipped. The sole skip is the mutually exclusive
missing-SDK entry-point path; all five SDK-bound `TestMcpBinding` cases ran and
passed against `mcp==1.28.1`, including supervised replay-store failure and
registry-to-history restart-gap propagation.
The installed suite also proves conservative process-epoch taint and a 4009
fresh-IDENTIFY boundary before the new session's first successor event.

The installed console `nunchi-mcp-discord --help` also completed. No Discord
credential was present in this review process, so no live receive/send or
mixed-room claim is made here. That separate lifecycle evidence remains
pending and cannot be inferred from this source/runtime record.
