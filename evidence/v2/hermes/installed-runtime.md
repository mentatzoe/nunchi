# Installed Hermes provenance — successor candidate 2026-07-21

## Inspected source

- Path: `/Users/zmll/.hermes/hermes-agent`
- Package version: `0.19.0`
- Git commit: `f657840e06e03b9552cf2d28175a1e4e4af0210b`
- Candidate base: `a03eeb95c7d569895e1171993c7a5748fc250bd8`
- Tracked source status before and after verification: clean

No candidate file was copied into the installed checkout. No package was
installed into the production venv. No gateway/profile/runtime configuration
was changed, and no service was restarted.

## Disposable verification method

Installed tests ran in fresh processes with:

```text
PYTHONDONTWRITEBYTECODE=1
PYTHONPATH=/tmp/nunchi-hermes-py311-pytest.Vroaus/site
/Users/zmll/.hermes/hermes-agent/venv/bin/python -m pytest -p no:cacheprovider
```

## Fresh results

- Platform commands: `50 passed, 4 skipped in 6.03s`.
- Session race guard and slash-auth suites: `60 tests passed in 5.91s`.
- Pending drain race plus pending drain no-recursion: `8 passed in 4.97s`.

- Discord roles/DM scope under the sanitized test environment:
  `15 passed in 0.18s`.
- The sanitized run unset only `DISCORD_ALLOWED_CHANNELS` and
  `DISCORD_IGNORED_CHANNELS`; it retained `PYTHONDONTWRITEBYTECODE=1` and
  `-p no:cacheprovider` and ran from the disposable pytest site.
- The earlier `14 passed, 1 failed` result was caused by inherited channel-scope
  environment contamination and is not an installed-Hermes limitation.

The successor does not claim an installed runtime cutover.
