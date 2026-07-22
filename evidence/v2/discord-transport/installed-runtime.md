# Discord V2 installed-runtime evidence

**Source commit:** `b46bc8a0fbba18a3af0fb401aefa431f1e953302`

**Evidence grade:** clean local wheel install plus exact SDK-bound deterministic
execution. This is not a live Discord-room claim.

The candidate was built and installed non-editably into the new virtual
environment `/private/tmp/nunchi-v2-050-rework.bFzHSK`:

```text
Python 3.14.3
nunchi=0.2.0
mcp=1.28.1
nunchi_path=/private/tmp/nunchi-v2-050-rework.bFzHSK/lib/python3.14/site-packages/nunchi/__init__.py
wheel_sha256=ceb9c22d41afad8d6ed54753d78e0cb19a18904c6f38f52ff8d3e8d7b08aeec1
```

Commands:

```sh
python3 -m venv /private/tmp/nunchi-v2-050-rework.bFzHSK
/private/tmp/nunchi-v2-050-rework.bFzHSK/bin/python -m pip install \
  --disable-pip-version-check '.[mcp-discord]'
PYTHONDONTWRITEBYTECODE=1 \
  /private/tmp/nunchi-v2-050-rework.bFzHSK/bin/python -m unittest -v \
  tests.test_mcp_discord_server \
  tests.v2.test_discord_transport \
  tests.test_mcp_discord_gateway \
  tests.v2.test_mcp_transport_client_v2
```

Result: `139` passed, `1` skipped. The sole skip is the mutually exclusive
missing-SDK entry-point path; all five SDK-bound `TestMcpBinding` cases ran and
passed against `mcp==1.28.1`, including supervised replay-store failure and
registry-to-history restart-gap propagation.

The installed console `nunchi-mcp-discord --help` also completed. No Discord
credential was present in this review process, so no live receive/send or
mixed-room claim is made here. That separate lifecycle evidence remains
pending and cannot be inferred from this source/runtime record.
