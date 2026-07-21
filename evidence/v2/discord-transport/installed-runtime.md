# Discord V2 installed-runtime evidence

**Source commit:** `fd2278e05b835bcaff0a93bf2fc681ab860c6a15`

**Evidence grade:** clean local wheel install plus exact SDK-bound deterministic
execution. This is not a live Discord-room claim.

The candidate was built and installed non-editably into the new virtual
environment `/private/tmp/nunchi-v2-050-installed`:

```text
Python 3.14.3
nunchi=0.2.0
mcp=1.28.1
nunchi_path=/private/tmp/nunchi-v2-050-installed/lib/python3.14/site-packages/nunchi/__init__.py
wheel_sha256=4f525309177764d3650b4d8ca8403be9ba8968f84314af05ca6e02f310024602
```

Commands:

```sh
python3 -m venv /private/tmp/nunchi-v2-050-installed
/private/tmp/nunchi-v2-050-installed/bin/python -m pip install \
  --disable-pip-version-check '.[mcp-discord]'
PYTHONDONTWRITEBYTECODE=1 \
  /private/tmp/nunchi-v2-050-installed/bin/python -m unittest -v \
  tests.test_mcp_discord_server \
  tests.v2.test_discord_transport \
  tests.test_mcp_discord_gateway \
  tests.v2.test_mcp_transport_client_v2
```

Result: `136` passed, `1` skipped. The sole skip is the mutually exclusive
missing-SDK entry-point path; all four SDK-bound `TestMcpBinding` cases ran and
passed against `mcp==1.28.1`, including replay-store behavior.

The installed console `nunchi-mcp-discord --help` also completed. No Discord
credential was present in this review process, so no live receive/send or
mixed-room claim is made here. That separate lifecycle evidence remains
pending and cannot be inferred from this source/runtime record.
