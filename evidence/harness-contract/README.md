# Harness contract spikes (2026-10-07)

Step 9b of [#94](https://github.com/mentatzoe/nunchi/issues/94). These are
throwaway checks behind `docs/harness-contract.md`, kept so the results can
be rerun. They are not part of Nunchi's test suite. They run on clean,
throwaway installs, never on anyone's own setup.

## Hermes: consume and start

`hermes_consume_and_start_spike.py` uses Hermes's own gateway test pattern:
the real `GatewayRunner` and adapter ingress, with only the model call
stubbed.

To run it:

1. Check out Hermes main (`a50406d9` here) and install it with
   `pip install -e ".[messaging]" pytest==9.1.1 pytest-asyncio==1.3.0`.
2. Copy the file into the Hermes checkout's `tests/gateway/`.
3. Run it with `pytest` there.

Result on `a50406d9`, Python 3.14.8:

- **Per-user group sessions (Hermes's default):** all checks pass.
- **Shared group sessions:** a person's message during an injected turn never
  reaches `post_gateway_admission`. This is the expected failure the
  contract records.

## Codex: trust written by `thread/start`

`codex_trust_spike.py` starts `codex app-server` with a fresh `CODEX_HOME` and
`HOME`, sends `initialize` and `thread/start` in several ways, and reports
whether the Codex config was written. It calls no model.

To run it:

```sh
mkdir -p spike/npm && (cd spike/npm && npm install @openai/codex@0.160.1)
python3 -I codex_trust_spike.py spike
```

Result with Codex CLI 0.160.1: only a thread with a `cwd` and a writable
sandbox, and no trust level in the thread's own `config`, writes
`trust_level = "trusted"` into the Codex config.
